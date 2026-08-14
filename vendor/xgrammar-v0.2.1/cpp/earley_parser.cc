/*!
 *  Copyright (c) 2025 by Contributors
 * \file xgrammar/earley_parser.cc
 *
 * Modified 2026-08-14 by the project3230617-388044 team: implement lossless ranged Earley
 * completion storage and propagation without identifier- or input-specific activation.
 */

#include "earley_parser.h"

#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <ctime>
#include <utility>
#include <vector>

#include "fsm.h"
#include "grammar_impl.h"
#include "support/encoding.h"
#include "support/logging.h"
#include "xgrammar/grammar.h"

namespace xgrammar {

using GrammarExprType = Grammar::Impl::GrammarExprType;

using GrammarExpr = Grammar::Impl::GrammarExpr;

bool CompletableStateHistory::SameCore(const ParserState& lhs, const ParserState& rhs) {
  return lhs.rule_id == rhs.rule_id && lhs.sequence_id == rhs.sequence_id &&
         lhs.element_id == rhs.element_id && lhs.sub_element_id == rhs.sub_element_id &&
         lhs.repeat_count == rhs.repeat_count && lhs.partial_codepoint == rhs.partial_codepoint;
}

void CompletableStateHistory::AppendRange(
    PackedRow* packed_row,
    int32_t ref_rule_id,
    const ParserState& state,
    int32_t begin,
    int32_t end
) {
  XGRAMMAR_DCHECK(begin <= end);
  XGRAMMAR_DCHECK(!packed_row->finalized);
  auto& row = packed_row->states;
  for (std::size_t index = 0; index < row.size();) {
    const auto& existing = row[index];
    const int64_t separated_before = static_cast<int64_t>(end) + 1;
    const int64_t separated_after = static_cast<int64_t>(existing.rule_start_pos_end) + 1;
    if (existing.ref_rule_id != ref_rule_id || !SameCore(existing.state, state) ||
        separated_before < existing.state.rule_start_pos || separated_after < begin) {
      ++index;
      continue;
    }
    begin = std::min(begin, existing.state.rule_start_pos);
    end = std::max(end, existing.rule_start_pos_end);
    row.erase(row.begin() + index);
  }
  auto exemplar = state;
  exemplar.rule_start_pos = begin;
  row.push_back(StateRange{ref_rule_id, exemplar, end});
}

void CompletableStateHistory::AppendRangeToLatest(
    int32_t ref_rule_id, const ParserState& state, int32_t begin, int32_t end
) {
  XGRAMMAR_DCHECK(!rows_.empty());
  AppendRange(&rows_.back(), ref_rule_id, state, begin, end);
}

void CompletableStateHistory::FinalizeRow(PackedRow* row) {
  if (row->finalized) return;
  std::stable_sort(row->states.begin(), row->states.end(), [](const auto& lhs, const auto& rhs) {
    return lhs.ref_rule_id < rhs.ref_rule_id;
  });
  row->finalized = true;
}

std::vector<CompletableStateHistory::StateRange>
CompletableStateHistory::MatchingRangesInRow(const PackedRow& row, int32_t ref_rule_id) {
  std::vector<StateRange> result;
  if (!row.finalized) {
    for (const auto& packed : row.states) {
      if (packed.ref_rule_id == ref_rule_id) result.push_back(packed);
    }
    return result;
  }
  const auto lower = std::lower_bound(
      row.states.begin(), row.states.end(), ref_rule_id, [](const auto& packed, int32_t ref) {
        return packed.ref_rule_id < ref;
      }
  );
  const auto upper = std::upper_bound(
      lower, row.states.end(), ref_rule_id, [](int32_t ref, const auto& packed) {
        return ref < packed.ref_rule_id;
      }
  );
  result.assign(lower, upper);
  return result;
}

void CompletableStateHistory::PushBack(const std::vector<StatePair>& states) {
  rows_.push_back(PackedRow{});
  for (const auto& [ref_rule_id, state] : states) {
    AppendRangeToLatest(ref_rule_id, state, state.rule_start_pos, state.rule_start_pos);
  }
}

void CompletableStateHistory::PushBackInLatestRow(const StatePair& state) {
  AppendRangeToLatest(
      state.first, state.second, state.second.rule_start_pos, state.second.rule_start_pos
  );
}

void CompletableStateHistory::PushRangeInLatestRow(
    int32_t ref_rule_id, const ParserState& state, int32_t rule_start_pos_end
) {
  AppendRangeToLatest(ref_rule_id, state, state.rule_start_pos, rule_start_pos_end);
}

void CompletableStateHistory::PushBackMergedRanges(
    const std::vector<StateRange>& lhs, const std::vector<StateRange>& rhs
) {
  rows_.push_back(PackedRow{});
  const auto append = [&](const std::vector<StateRange>& source) {
    for (const auto& packed : source) {
      AppendRangeToLatest(
          packed.ref_rule_id,
          packed.state,
          packed.state.rule_start_pos,
          packed.rule_start_pos_end
      );
    }
  };
  append(lhs);
  append(rhs);
  FinalizeLatestRow();
}

void CompletableStateHistory::FinalizeLatestRow() {
  XGRAMMAR_DCHECK(!rows_.empty());
  FinalizeRow(&rows_.back());
  MaybeBuildBlockSummary();
}

void CompletableStateHistory::MaybeBuildBlockSummary() {
  if (rows_.size() % kBlockSize != 0) {
    return;
  }
  if (block_levels_.empty()) block_levels_.resize(1);
  const std::size_t block_count = rows_.size() / kBlockSize;
  if (block_levels_[0].size() == block_count) return;
  PackedRow summary;
  const std::size_t begin = rows_.size() - kBlockSize;
  for (std::size_t position = begin; position < rows_.size(); ++position) {
    XGRAMMAR_DCHECK(rows_[position].finalized);
    for (const auto& packed : rows_[position].states) {
      AppendRange(
          &summary,
          packed.ref_rule_id,
          packed.state,
          packed.state.rule_start_pos,
          packed.rule_start_pos_end
      );
    }
  }
  FinalizeRow(&summary);
  block_levels_[0].push_back(std::move(summary));

  for (std::size_t level = 1, width = 2; block_count % width == 0;
       ++level, width *= 2) {
    if (block_levels_.size() <= level) block_levels_.resize(level + 1);
    const auto& children = block_levels_[level - 1];
    const std::size_t right_index = block_count / (width / 2) - 1;
    const std::size_t left_index = right_index - 1;
    PackedRow parent;
    for (const std::size_t child_index : {left_index, right_index}) {
      for (const auto& packed : children[child_index].states) {
        AppendRange(
            &parent,
            packed.ref_rule_id,
            packed.state,
            packed.state.rule_start_pos,
            packed.rule_start_pos_end
        );
      }
    }
    FinalizeRow(&parent);
    block_levels_[level].push_back(std::move(parent));
  }
}

void CompletableStateHistory::PopBack(int32_t count) {
  XGRAMMAR_DCHECK(count >= 0 && count <= size());
  rows_.erase(rows_.end() - count, rows_.end());
  const std::size_t block_count = rows_.size() / kBlockSize;
  for (std::size_t level = 0, width = 1; level < block_levels_.size();
       ++level, width *= 2) {
    block_levels_[level].resize(block_count / width);
  }
  while (!block_levels_.empty() && block_levels_.back().empty()) block_levels_.pop_back();
}

std::vector<CompletableStateHistory::StatePair> CompletableStateHistory::ExpandRow(
    int32_t position
) const {
  XGRAMMAR_DCHECK(position >= 0 && position < size());
  std::vector<StatePair> result;
  std::size_t expanded_size = 0;
  for (const auto& packed : rows_[position].states) {
    expanded_size += static_cast<std::size_t>(
        static_cast<int64_t>(packed.rule_start_pos_end) - packed.state.rule_start_pos + 1
    );
  }
  result.reserve(expanded_size);
  for (const auto& packed : rows_[position].states) {
    for (int32_t start = packed.state.rule_start_pos;; ++start) {
      auto state = packed.state;
      state.rule_start_pos = start;
      result.push_back({packed.ref_rule_id, state});
      if (start == packed.rule_start_pos_end) break;
    }
  }
  return result;
}

std::vector<CompletableStateHistory::StateRange> CompletableStateHistory::MatchingRanges(
    int32_t position, int32_t ref_rule_id
) const {
  XGRAMMAR_DCHECK(position >= 0 && position < size());
  return MatchingRangesInRow(rows_[position], ref_rule_id);
}

std::vector<CompletableStateHistory::StateRange>
CompletableStateHistory::MatchingRangesAcrossRows(
    int32_t position_begin, int32_t position_end, int32_t ref_rule_id
) const {
  XGRAMMAR_DCHECK(position_begin >= 0 && position_begin <= position_end && position_end < size());
  PackedRow summary;
  const auto append_source = [&](const PackedRow& source) {
    for (const auto& packed : MatchingRangesInRow(source, ref_rule_id)) {
      AppendRange(
          &summary,
          packed.ref_rule_id,
          packed.state,
          packed.state.rule_start_pos,
          packed.rule_start_pos_end
      );
    }
  };

  int32_t position = position_begin;
  const int32_t finalized_count =
      size() - (!rows_.empty() && !rows_.back().finalized ? 1 : 0);
  while (position <= position_end && position % kBlockSize != 0) {
    append_source(rows_[position++]);
  }
  while (position + kBlockSize - 1 <= position_end &&
         position + kBlockSize <= finalized_count) {
    const std::size_t block_index = static_cast<std::size_t>(position / kBlockSize);
    const std::size_t remaining_blocks =
        static_cast<std::size_t>((position_end - position + 1) / kBlockSize);
    std::size_t level = 0;
    while ((std::size_t{1} << (level + 1)) <= remaining_blocks &&
           block_index % (std::size_t{1} << (level + 1)) == 0) {
      ++level;
    }
    XGRAMMAR_DCHECK(level < block_levels_.size());
    const std::size_t node_index = block_index >> level;
    XGRAMMAR_DCHECK(node_index < block_levels_[level].size());
    append_source(block_levels_[level][node_index]);
    position += static_cast<int32_t>(kBlockSize * (std::size_t{1} << level));
  }
  while (position <= position_end) append_source(rows_[position++]);
  FinalizeRow(&summary);
  return summary.states;
}

void CompletableStateHistory::CopyRuleStatesToLatest(
    int32_t source_position, int32_t source_rule_id, int32_t target_rule_id
) {
  XGRAMMAR_DCHECK(source_position >= 0 && source_position < size() - 1);
  const auto selected = MatchingRanges(source_position, source_rule_id);
  for (const auto& packed : selected) {
    AppendRangeToLatest(
        target_rule_id,
        packed.state,
        packed.state.rule_start_pos,
        packed.rule_start_pos_end
    );
  }
}

void CompletableStateHistory::CopyRuleStatesRangeToLatest(
    int32_t source_position_begin,
    int32_t source_position_end,
    int32_t source_rule_id,
    int32_t target_rule_id
) {
  XGRAMMAR_DCHECK(source_position_begin <= source_position_end);
  XGRAMMAR_DCHECK(source_position_begin >= 0 && source_position_end < size() - 1);
  for (const auto& packed : MatchingRangesAcrossRows(
           source_position_begin, source_position_end, source_rule_id
       )) {
    AppendRangeToLatest(
        target_rule_id,
        packed.state,
        packed.state.rule_start_pos,
        packed.rule_start_pos_end
    );
  }
}

std::vector<QueuedParserState> RangeRepeatDetector::InsertUnvisited(
    const ParserState& state, int32_t rule_start_pos_end
) {
  XGRAMMAR_DCHECK(state.rule_start_pos <= rule_start_pos_end);
  auto& covered = visited_[state];
  std::vector<Interval> uncovered{{state.rule_start_pos, rule_start_pos_end}};
  for (const auto& existing : covered) {
    std::vector<Interval> next;
    for (const auto& segment : uncovered) {
      if (existing.second < segment.first || existing.first > segment.second) {
        next.push_back(segment);
        continue;
      }
      if (segment.first < existing.first) {
        next.push_back({segment.first, static_cast<int32_t>(existing.first - 1)});
      }
      if (existing.second < segment.second) {
        next.push_back({static_cast<int32_t>(existing.second + 1), segment.second});
      }
    }
    uncovered = std::move(next);
    if (uncovered.empty()) break;
  }

  covered.push_back({state.rule_start_pos, rule_start_pos_end});
  std::sort(covered.begin(), covered.end());
  std::vector<Interval> merged;
  for (const auto& interval : covered) {
    if (merged.empty() ||
        static_cast<int64_t>(merged.back().second) + 1 < interval.first) {
      merged.push_back(interval);
    } else {
      merged.back().second = std::max(merged.back().second, interval.second);
    }
  }
  covered = std::move(merged);

  std::vector<QueuedParserState> result;
  for (const auto& interval : uncovered) {
    auto exemplar = state;
    exemplar.rule_start_pos = interval.first;
    result.push_back({exemplar, interval.second});
  }
  return result;
}

void RangeWorkQueue::AddInterval(
    std::vector<Interval>* intervals, Interval added, int32_t current_position
) {
  intervals->push_back(added);
  std::sort(intervals->begin(), intervals->end());
  std::vector<Interval> merged;
  for (const auto& interval : *intervals) {
    bool keep_separate = merged.empty();
    if (!merged.empty()) {
      const int64_t next = static_cast<int64_t>(merged.back().second) + 1;
      const bool crosses_root = merged.back().second == ParserState::kNoPrevInputPos &&
                                interval.first == 0;
      const bool crosses_current = next == current_position;
      keep_separate = next < interval.first ||
                      (next == interval.first && (crosses_root || crosses_current));
    }
    if (keep_separate) {
      merged.push_back(interval);
    } else {
      merged.back().second = std::max(merged.back().second, interval.second);
    }
  }
  *intervals = std::move(merged);
}

void RangeWorkQueue::Push(const QueuedParserState& delta, int32_t current_position) {
  const auto found = pending_.find(delta.state);
  if (found == pending_.end()) {
    Item item{delta.state, {}};
    AddInterval(
        &item.intervals,
        {delta.state.rule_start_pos, delta.rule_start_pos_end},
        current_position
    );
    items_.push_back(std::move(item));
    auto iterator = std::prev(items_.end());
    pending_.emplace(iterator->state, iterator);
    return;
  }
  AddInterval(
      &found->second->intervals,
      {delta.state.rule_start_pos, delta.rule_start_pos_end},
      current_position
  );
}

RangeWorkQueue::Item RangeWorkQueue::PopFront() {
  XGRAMMAR_DCHECK(!items_.empty());
  Item result = std::move(items_.front());
  pending_.erase(result.state);
  items_.pop_front();
  return result;
}

void EarleyParser::EnqueueRange(const ParserState& state, int32_t rule_start_pos_end) {
  XGRAMMAR_DCHECK(state.rule_start_pos <= rule_start_pos_end);
  std::vector<std::pair<int32_t, int32_t>> segments{
      {state.rule_start_pos, rule_start_pos_end}
  };
  const auto split_at = [&](int32_t special) {
    std::vector<std::pair<int32_t, int32_t>> split;
    for (const auto& [begin, end] : segments) {
      if (special < begin || special > end) {
        split.push_back({begin, end});
        continue;
      }
      if (begin < special) split.push_back({begin, static_cast<int32_t>(special - 1)});
      split.push_back({special, special});
      if (special < end) split.push_back({static_cast<int32_t>(special + 1), end});
    }
    segments = std::move(split);
  };
  split_at(ParserState::kNoPrevInputPos);
  if (rule_id_to_completable_states_.size() > 0) {
    split_at(rule_id_to_completable_states_.size() - 1);
  }
  for (const auto& [begin, end] : segments) {
    auto exemplar = state;
    exemplar.rule_start_pos = begin;
    for (const auto& delta : tmp_states_visited_in_queue_.InsertUnvisited(exemplar, end)) {
      tmp_process_state_queue_.Push(
          delta,
          rule_id_to_completable_states_.size() > 0
              ? rule_id_to_completable_states_.size() - 1
              : ParserState::kNoPrevInputPos
      );
    }
  }
}

void EarleyParser::AppendScannableRange(
    const ParserState& state, int32_t rule_start_pos_end
) {
  for (int32_t start = state.rule_start_pos;; ++start) {
    auto expanded = state;
    expanded.rule_start_pos = start;
    tmp_states_to_be_added_.push_back(expanded);
    if (start == rule_start_pos_end) break;
  }
}

void EarleyParser::StoreCompletableState(int32_t ref_rule_id, const ParserState& state) {
  const int32_t end =
      processing_range_ && state.rule_start_pos == processing_range_begin_
      ? processing_range_end_
      : state.rule_start_pos;
  rule_id_to_completable_states_.PushRangeInLatestRow(ref_rule_id, state, end);
}

bool EarleyParser::IsCompleted() const { return is_completed_.back(); }

void EarleyParser::PopLastStates(int32_t cnt) {
  if (stop_token_is_accepted_) {
    stop_token_is_accepted_ = false;
  }
  if (cnt >= static_cast<int32_t>(rule_id_to_completable_states_.size())) {
    XGRAMMAR_LOG(FATAL) << "The number of states to be popped is larger than the size of states.";
  }
  rule_id_to_completable_states_.PopBack(cnt);
  is_completed_.erase(is_completed_.end() - cnt, is_completed_.end());
  scanable_state_history_.PopBack(cnt);
}

void EarleyParser::Complete(const ParserState& state, bool debug_print) {
  // Check if a rule is completed.
  if (state.rule_start_pos == ParserState::kNoPrevInputPos) {
    // assert: if a root rule can achieve here, then it must be completed.
    if (debug_print) {
      XGRAMMAR_LOG(INFO) << "The root rule is completed.";
    }
    tmp_accept_stop_token_ = true;
    return;
  }
  if (debug_print) {
    XGRAMMAR_LOG(INFO) << "The rule " << state.rule_id << ": "
                       << grammar_->GetRule(state.rule_id).name
                       << " is completed, trying to complete its parent states.";
  }

  // Check all possible parent-state ranges without expanding rule_start_pos.
  const int32_t completed_end =
      processing_range_ && state.rule_start_pos == processing_range_begin_
      ? processing_range_end_
      : state.rule_start_pos;
  const auto parent_ranges = rule_id_to_completable_states_.MatchingRangesAcrossRows(
      state.rule_start_pos, completed_end, state.rule_id
  );
    for (const auto& parent_range : parent_ranges) {
      const int32_t ref_id = parent_range.ref_rule_id;
      const auto& parent_state = parent_range.state;
      const auto enqueue_parent = [&](const ParserState& next_state) {
        const int32_t end = next_state.rule_start_pos == parent_state.rule_start_pos
                                ? parent_range.rule_start_pos_end
                                : next_state.rule_start_pos;
        EnqueueRange(next_state, end);
      };
    XGRAMMAR_DCHECK(
        parent_state.rule_id == -1 || grammar_->per_rule_fsms[parent_state.rule_id].has_value()
    );
    if (parent_state.rule_id == -1) {
      const auto& parent_expr = grammar_->GetGrammarExpr(parent_state.sequence_id);
      const auto& element_expr = grammar_->GetGrammarExpr(parent_expr[parent_state.element_id]);
      // The new rule is not referenced by a fsm.
      XGRAMMAR_DCHECK(
          element_expr.type == GrammarExprType::kRuleRef ||
          element_expr.type == GrammarExprType::kRepeat
      );
      if (element_expr.type == GrammarExprType::kRuleRef) {
        enqueue_parent(ParserState{
            parent_state.rule_id,
            parent_state.sequence_id,
            parent_state.element_id + 1,
            parent_state.rule_start_pos,
            0
        });
        continue;
      }
      XGRAMMAR_DCHECK(element_expr.type == GrammarExprType::kRepeat);
      // The parent state is a repeat, we need to increase the repeat count.
      auto new_state = parent_state;
      const int32_t& min_repeat_count = element_expr[1];
      const int32_t& max_repeat_count = element_expr[2];
      new_state.repeat_count++;
      // The repeat rule can be completed, and we advance the state. Don't forget to
      // reset the repeat count.
      if (new_state.repeat_count >= min_repeat_count) {
        enqueue_parent(ParserState{
            parent_state.rule_id,
            parent_state.sequence_id,
            parent_state.element_id + 1,
            parent_state.rule_start_pos,
            0
        });
      }
      // If the repeat count is less than the max repeat count, we can continue to
      // visit the repeat state for another round.
      if (new_state.repeat_count < max_repeat_count) {
        enqueue_parent(new_state);
      }
      continue;
    }
    // If the rule is referenced by a fsm, we need to advance the fsm.
    XGRAMMAR_DCHECK(grammar_->per_rule_fsms[parent_state.rule_id].has_value());

    // Check if the parent_state sits on a kRepeatRef edge
    bool handled_as_repeat = false;
    const auto& parent_fsm = grammar_->per_rule_fsms[parent_state.rule_id].value();
    for (const auto& edge : parent_fsm.GetFsm().GetFsm().GetEdges(parent_state.element_id)) {
      // Because of invariance, a state with a kRepeatRef edge has exactly one outgoing edge.
      if (!edge.IsRepeatRef()) continue;
      auto info = grammar_->complete_fsm.GetRepeatEdgeInfo(edge.GetAuxIndex());
      if (info.RuleId() != ref_id) continue;
      handled_as_repeat = true;
      int32_t new_count = parent_state.repeat_count + 1;
      if (new_count >= info.Lower()) {
        enqueue_parent(ParserState{
            parent_state.rule_id,
            parent_state.sequence_id,
            edge.target,
            parent_state.rule_start_pos,
            0,
            0
        });
      }
      if (new_count < info.Upper()) {
        enqueue_parent(ParserState{
            parent_state.rule_id,
            parent_state.sequence_id,
            parent_state.element_id,
            parent_state.rule_start_pos,
            0,
            new_count
        });
      }
      break;
    }
    if (!handled_as_repeat) {
      enqueue_parent(parent_state);
    }
    }
}

std::pair</* scanable */ bool, /* completable */ bool> EarleyParser::Predict(
    const ParserState& state, bool debug_print
) {
  // Check if the rule has a corresponding FSM.
  if (state.rule_id != -1) {
    XGRAMMAR_DCHECK(grammar_->per_rule_fsms[state.rule_id].has_value());
    // Try to expand the fsm.
    ExpandNextRuleRefElementOnFSM(state, debug_print);
    const auto& fsm = grammar_->per_rule_fsms[state.rule_id].value();
    return std::make_pair(
        fsm.GetFsm().IsScanableState(state.element_id), fsm.GetFsm().IsEndState(state.element_id)
    );
  }
  const GrammarExpr& grammar_expr = grammar_->GetGrammarExpr(state.sequence_id);
  XGRAMMAR_DCHECK(
      grammar_expr.type == GrammarExprType::kSequence ||
      grammar_expr.type == GrammarExprType::kEmptyStr
  );
  if (state.element_id == grammar_expr.size()) {
    // The rule is completed.
    return std::make_pair(false, true);
  }
  const auto& element_expr = grammar_->GetGrammarExpr(grammar_expr[state.element_id]);
  switch (element_expr.type) {
    case GrammarExprType::kRuleRef: {
      ExpandNextRuleRefElement(state, grammar_expr, &element_expr, debug_print);
      return std::make_pair(false, false);
    }
    case GrammarExprType::kCharacterClassStar: {
      if (state.sub_element_id == 0) {
        Enqueue(ParserState{
            state.rule_id, state.sequence_id, state.element_id + 1, state.rule_start_pos, 0
        });
      }
      return std::make_pair(true, false);
    }
    case GrammarExprType::kRepeat: {
      const int32_t& min_repeat_count = element_expr[1];
      const int32_t& max_repeat_count = element_expr[2];
      // If the current repeat count is less than the max repeat count,
      // we can expand the next rule reference element.
      XGRAMMAR_DCHECK(state.repeat_count <= max_repeat_count);
      ExpandNextRuleRefElement(state, grammar_expr, &element_expr, debug_print);
      if (state.repeat_count >= min_repeat_count) {
        Enqueue(ParserState{
            state.rule_id, state.sequence_id, state.element_id + 1, state.rule_start_pos, 0
        });
      }
      return std::make_pair(false, false);
    }
    case GrammarExprType::kByteString:
    case GrammarExprType::kCharacterClass: {
      return std::make_pair(true, false);  // The element is scanable, but not completable.
    }
    case GrammarExprType::kToken:
    case GrammarExprType::kExcludeToken: {
      return std::make_pair(false, false);
    }
    default: {
      XGRAMMAR_LOG(FATAL) << "The element type is not supported! The type is: "
                          << int(element_expr.type);
      XGRAMMAR_UNREACHABLE();
    }
  }
}

void EarleyParser::Scan(const ParserState& state, const uint8_t ch) {
  XGRAMMAR_DCHECK(state.rule_id == -1 || grammar_->per_rule_fsms[state.rule_id].has_value());
  if (state.rule_id == -1) {
    const auto& cur_rule = grammar_->GetGrammarExpr(state.sequence_id);
    const auto& element_expr = grammar_->GetGrammarExpr(cur_rule[state.element_id]);
    // The element is a rule reference, we do not need to scan it.
    switch (element_expr.type) {
      case (GrammarExprType::kByteString): {
        AdvanceByteString(state, ch, element_expr);
        break;
      }
      case (GrammarExprType::kCharacterClass): {
        AdvanceCharacterClass(state, ch, element_expr);
        break;
      }
      case (GrammarExprType::kCharacterClassStar): {
        AdvanceCharacterClassStar(state, ch, element_expr);
        break;
      }
      default: {
        XGRAMMAR_LOG(FATAL) << "The element type is not supported! The type is: "
                            << int(element_expr.type);
        XGRAMMAR_UNREACHABLE();
      }
    }
  } else {
    AdvanceFsm(state, ch);
  }
}

/*!
  \note The workflow of Advance is as follows:
  1. Scan all the states in the latest states. Add all the possible states
  to the next states.
  2. If the next states are empty, then the character is not accepted.
  3. If the next states are not empty, then the character is accepted. Moreover,
  we need to complete and predict the next states.

  \note Thus, when initializing the Earley parser, we need to add the initial state
  to the history_states[0], and perform prediction and completion on the initial state.
*/
bool EarleyParser::Advance(const uint8_t ch, bool debug_print) {
  // Initialize the containers.
  XGRAMMAR_DCHECK(tmp_process_state_queue_.empty())
      << "The tmp_process_state_queue_ should be empty before the scan.";
  tmp_states_visited_in_queue_.Clear();
  tmp_states_to_be_added_.clear();
  tmp_accept_stop_token_ = false;
  const auto& latest_states = scanable_state_history_[scanable_state_history_.size() - 1];
  // Scan all the scanable states.
  for (const auto& state : latest_states) {
    Scan(state, ch);
  }

  // Check if the character is accepted.
  if (tmp_process_state_queue_.empty() && tmp_states_to_be_added_.empty()) {
    return false;
  }

  // execute Predict and Complete for all states in the queue until empty.
  rule_id_to_completable_states_.PushBack(std::vector<std::pair<int32_t, ParserState>>());
  while (!tmp_process_state_queue_.empty()) {
    auto queued = tmp_process_state_queue_.PopFront();
    for (const auto& [begin, end] : queued.intervals) {
      auto state = queued.state;
      state.rule_start_pos = begin;
      processing_range_ = true;
      processing_range_begin_ = begin;
      processing_range_end_ = end;
      auto [scanable, completable] = Predict(state, debug_print);
      if (completable) {
        Complete(state, debug_print);
      }
      if (scanable) {
        AppendScannableRange(state, end);
      }
      processing_range_ = false;
    }
  }
  rule_id_to_completable_states_.FinalizeLatestRow();

  // Check if the grammar is completed, and add the scannable states to the history.
  is_completed_.push_back(tmp_accept_stop_token_);
  scanable_state_history_.PushBack(tmp_states_to_be_added_);
  return true;
}

EarleyParser::EarleyParser(
    const Grammar& grammar, const ParserState& init_state, const bool need_expand
)
    : grammar_(grammar) {
  if (!grammar->optimized) {
    XGRAMMAR_LOG(FATAL) << "The grammar is not optimized. Please optimize the grammar before using "
                           "the Earley parser.";
  }
  // Check if the initial state is valid. If invalid, then we choose the root state as default.
  ParserState init = init_state;
  if (init_state.IsInvalid()) {
    init = ParserState(
        grammar_->GetRootRuleId(),
        ParserState::kUnexpandedRuleStartSequenceId,
        0,
        ParserState::kNoPrevInputPos,
        0
    );
  } else {
    init = init_state;
  }

  // If there is no need to expand the initial state, we only need to add it to the
  // scanable states history.
  if (!need_expand) {
    rule_id_to_completable_states_.PushBack(std::vector<std::pair<int32_t, ParserState>>());
    rule_id_to_completable_states_.FinalizeLatestRow();
    is_completed_.push_back(false);
    scanable_state_history_.PushBack({init});
    return;
  }

  // Otherwise, we expand the initial state, and process the queue.
  PushStateAndExpand(init);
}

void EarleyParser::PushStateAndExpand(const ParserState& state) {
  tmp_states_visited_in_queue_.Clear();
  tmp_accept_stop_token_ = false;
  tmp_states_to_be_added_.clear();
  // If the rule can't be expanded, we need to add it to the queue.
  if (!ExpandAndEnqueueUnexpandedState(state)) {
    Enqueue(state);
  }
  rule_id_to_completable_states_.PushBack(std::vector<std::pair<int32_t, ParserState>>());
  while (!tmp_process_state_queue_.empty()) {
    auto queued = tmp_process_state_queue_.PopFront();
    for (const auto& [begin, end] : queued.intervals) {
      auto current_state = queued.state;
      current_state.rule_start_pos = begin;
      processing_range_ = true;
      processing_range_begin_ = begin;
      processing_range_end_ = end;
      auto [scanable, completable] = Predict(current_state);
      if (completable) {
        Complete(current_state);
      }
      if (scanable) {
        AppendScannableRange(current_state, end);
      }
      processing_range_ = false;
    }
  }
  rule_id_to_completable_states_.FinalizeLatestRow();
  is_completed_.push_back(tmp_accept_stop_token_);
  scanable_state_history_.PushBack(tmp_states_to_be_added_);
}

void EarleyParser::Reset() {
  rule_id_to_completable_states_.PopBack(rule_id_to_completable_states_.size());
  scanable_state_history_.PopBack(scanable_state_history_.size());
  is_completed_.clear();
  stop_token_is_accepted_ = false;
  XGRAMMAR_DCHECK(tmp_process_state_queue_.empty());
  PushStateAndExpand(ParserState(
      grammar_->GetRootRuleId(),
      ParserState::kUnexpandedRuleStartSequenceId,
      0,
      ParserState::kNoPrevInputPos,
      0
  ));
}

bool EarleyParser::ExpandAndEnqueueUnexpandedState(const ParserState& state) {
  if (state.sequence_id != ParserState::kUnexpandedRuleStartSequenceId) {
    return false;
  }
  auto cur_rule_id = state.rule_id;
  auto cur_rule_body_id = grammar_->GetRule(cur_rule_id).body_expr_id;
  XGRAMMAR_DCHECK(state.rule_id != -1 && grammar_->per_rule_fsms[state.rule_id].has_value());
  Enqueue(ParserState{
      cur_rule_id,
      cur_rule_body_id,
      grammar_->per_rule_fsms[state.rule_id]->GetFsm().GetStart(),
      ParserState::kNoPrevInputPos,
      0
  });
  return true;
}

void EarleyParser::ExpandNextRuleRefElement(
    const ParserState& state,
    const GrammarExpr& grammar_expr,
    const GrammarExpr* sub_grammar_expr,
    bool debug_print
) {
  // Path A. The rule has a corresponding FSM.
  XGRAMMAR_DCHECK(!(state.rule_id != -1 && grammar_->per_rule_fsms[state.rule_id].has_value()));
  XGRAMMAR_DCHECK(grammar_expr.type == GrammarExprType::kSequence);
  XGRAMMAR_DCHECK(
      sub_grammar_expr->type == GrammarExprType::kRuleRef ||
      sub_grammar_expr->type == GrammarExprType::kRepeat
  );
  auto ref_rule_id = (*sub_grammar_expr)[0];

  if (debug_print) {
    XGRAMMAR_LOG(INFO) << "The rule " << state.rule_id << ": "
                       << grammar_->GetRule(state.rule_id).name << " predict the new rule "
                       << ref_rule_id << ": " << grammar_->GetRule(ref_rule_id).name << ".";
  }

  bool right_recursion_to_root = false;
  if (state.element_id != grammar_expr.size() - 1 ||
      sub_grammar_expr->type == GrammarExprType::kRepeat ||
      (state.rule_start_pos == rule_id_to_completable_states_.size() - 1)) {
    // It's not the right recursion, or it's the root rule.
    StoreCompletableState(ref_rule_id, state);
  } else {
    if (state.rule_start_pos == ParserState::kNoPrevInputPos) {
      right_recursion_to_root = true;
    } else {
      // If it's the right recursion, we need to add the ancestors of the parent state.
      const int32_t source_end =
          processing_range_ && state.rule_start_pos == processing_range_begin_
          ? processing_range_end_
          : state.rule_start_pos;
      rule_id_to_completable_states_.CopyRuleStatesRangeToLatest(
          state.rule_start_pos, source_end, state.rule_id, ref_rule_id
      );
    }
  }

  if (std::find(
          grammar_->allow_empty_rule_ids.begin(), grammar_->allow_empty_rule_ids.end(), ref_rule_id
      ) != grammar_->allow_empty_rule_ids.end()) {
    XGRAMMAR_DCHECK(grammar_expr.type == GrammarExprType::kSequence);
    Enqueue(
        ParserState{state.rule_id, state.sequence_id, state.element_id + 1, state.rule_start_pos, 0}
    );
  }

  // If the reference rule is not visited, we need to add it to the queue.
  const auto& ref_rule = grammar_->GetRule(ref_rule_id);
  const auto& ref_grammar_expr_id = ref_rule.body_expr_id;

  XGRAMMAR_DCHECK(grammar_->per_rule_fsms[ref_rule_id].has_value());
  if (std::find(
          grammar_->allow_empty_rule_ids.begin(), grammar_->allow_empty_rule_ids.end(), ref_rule_id
      ) != grammar_->allow_empty_rule_ids.end()) {
    Enqueue(
        ParserState{state.rule_id, state.sequence_id, state.element_id + 1, state.rule_start_pos, 0}
    );
  }
  const auto& ref_fsm = grammar_->per_rule_fsms[ref_rule_id].value();
  Enqueue(ParserState{
      ref_rule_id,
      ref_grammar_expr_id,
      ref_fsm.GetFsm().GetStart(),
      right_recursion_to_root ? ParserState::kNoPrevInputPos
                              : int32_t(rule_id_to_completable_states_.size() - 1),
      0
  });
}

void EarleyParser::ExpandNextRuleRefElementOnFSM(const ParserState& state, bool debug_print) {
  XGRAMMAR_DCHECK(state.rule_id != -1 && grammar_->per_rule_fsms[state.rule_id].has_value());
  const auto& fsm = grammar_->per_rule_fsms[state.rule_id].value();

  // Add the rule reference pairs, and enqueue the epsilon edges.
  for (const auto& edge : fsm.GetFsm().GetFsm().GetEdges(state.element_id)) {
    if (edge.IsEpsilon()) {
      Enqueue(ParserState{state.rule_id, state.sequence_id, edge.target, state.rule_start_pos, 0});
      continue;
    }

    int target;
    int ref_rule_id;
    bool is_repeat = false;
    RepeatEdgeRef repeat_info{nullptr};

    if (edge.IsRuleRef()) {
      target = edge.target;
      ref_rule_id = edge.GetRefRuleId();
    } else if (edge.IsRepeatRef()) {
      is_repeat = true;
      repeat_info = grammar_->complete_fsm.GetRepeatEdgeInfo(edge.GetAuxIndex());
      target = edge.target;
      ref_rule_id = repeat_info.RuleId();

      if (state.repeat_count >= repeat_info.Lower()) {
        Enqueue(ParserState{state.rule_id, state.sequence_id, target, state.rule_start_pos, 0, 0});
      }
      if (state.repeat_count >= repeat_info.Upper()) {
        continue;
      }
    } else {
      continue;
    }
    bool right_recursion_to_root = false;
    if (debug_print) {
      XGRAMMAR_LOG(INFO) << "The rule " << state.rule_id << ": "
                         << grammar_->GetRule(state.rule_id).name << " predict the new rule "
                         << ref_rule_id << ": " << grammar_->GetRule(ref_rule_id).name << ".";
    }
    if (!is_repeat && (fsm.GetFsm().GetFsm().GetEdges(target).size() == 0) &&
        fsm.GetFsm().IsEndState(target) &&
        state.rule_start_pos != static_cast<int32_t>(rule_id_to_completable_states_.size() - 1)) {
      // It's a right recursion. We can optimize it.
      // If it's the right recursion, we need to add the ancestors of the parent state.
      if (state.rule_start_pos == ParserState::kNoPrevInputPos) {
        // In this case, we can mark the new state as the root state to speed up.
        right_recursion_to_root = true;
      } else {
        const int32_t source_end =
            processing_range_ && state.rule_start_pos == processing_range_begin_
            ? processing_range_end_
            : state.rule_start_pos;
        rule_id_to_completable_states_.CopyRuleStatesRangeToLatest(
            state.rule_start_pos, source_end, state.rule_id, ref_rule_id
        );
      }
    } else {
      if (is_repeat) {
        // For kRepeatRef: store element_id = source state, preserve repeat_count
        StoreCompletableState(
            ref_rule_id,
            ParserState{
                state.rule_id,
                state.sequence_id,
                state.element_id,
                state.rule_start_pos,
                0,
                state.repeat_count
            }
        );
      } else {
        // For kRuleRef: store element_id = target (post-transition state)
        StoreCompletableState(
            ref_rule_id,
            ParserState{state.rule_id, state.sequence_id, target, state.rule_start_pos, 0}
        );
      }
    }

    // Check if the reference rule can be empty.
    if (!is_repeat && std::binary_search(
                          grammar_->allow_empty_rule_ids.begin(),
                          grammar_->allow_empty_rule_ids.end(),
                          ref_rule_id
                      )) {
      Enqueue(ParserState{state.rule_id, state.sequence_id, target, state.rule_start_pos, 0});
    }

    // If the reference rule is not visited, we need to add it to the queue.
    const auto& ref_rule = grammar_->GetRule(ref_rule_id);
    const auto& ref_grammar_expr_id = ref_rule.body_expr_id;

    XGRAMMAR_DCHECK(grammar_->per_rule_fsms[ref_rule_id].has_value());
    if (!is_repeat && std::binary_search(
                          grammar_->allow_empty_rule_ids.begin(),
                          grammar_->allow_empty_rule_ids.end(),
                          ref_rule_id
                      )) {
      Enqueue(ParserState{state.rule_id, state.sequence_id, target, state.rule_start_pos, 0});
    }
    const auto& ref_fsm = grammar_->per_rule_fsms[ref_rule_id].value();
    Enqueue(ParserState{
        ref_rule_id,
        ref_grammar_expr_id,
        ref_fsm.GetFsm().GetStart(),
        right_recursion_to_root ? ParserState::kNoPrevInputPos
                                : int32_t(rule_id_to_completable_states_.size() - 1),
        0
    });
  }
}

void EarleyParser::AdvanceByteString(
    const ParserState& state, const uint8_t ch, const GrammarExpr& sub_rule
) {
  XGRAMMAR_DCHECK(sub_rule.type == GrammarExprType::kByteString);
  XGRAMMAR_DCHECK(sub_rule.size() > state.sub_element_id);
  if (static_cast<uint8_t>(sub_rule[state.sub_element_id]) == ch) {
    auto new_state = state;
    new_state.sub_element_id++;
    if (new_state.sub_element_id == sub_rule.size()) {
      new_state.element_id++;
      new_state.sub_element_id = 0;
      Enqueue(new_state);
      // Assert: In a sequence, the bytestring can't be skipped. So the state can't be repeated.
    } else {
      tmp_states_to_be_added_.push_back(new_state);
    }
  }
  return;
}

void EarleyParser::AdvanceCharacterClass(
    const ParserState& state, const uint8_t ch, const GrammarExpr& sub_sequence
) {
  XGRAMMAR_DCHECK(sub_sequence.type == GrammarExprType::kCharacterClass)
      << "The element type is not supported!";

  bool is_negative = static_cast<bool>(sub_sequence[0]);

  // The state is matching a UTF8 character (continuation bytes).
  if (state.sub_element_id > 0) {
    if ((ch & 0xC0) == 0x80) {
      auto new_state = state;
      new_state.sub_element_id--;
      // Accumulate the codepoint from continuation byte
      new_state.partial_codepoint = (new_state.partial_codepoint << 6) | (ch & 0x3F);

      // Check if the UTF8 character is completed.
      if (new_state.sub_element_id == 0) {
        if (is_negative) {
          // For negative classes, accept if codepoint is NOT in any range
          bool matches_range = false;
          for (int i = 1; i < sub_sequence.size(); i += 2) {
            if (new_state.partial_codepoint >= sub_sequence[i] &&
                new_state.partial_codepoint <= sub_sequence[i + 1]) {
              matches_range = true;
              break;
            }
          }
          if (!matches_range) {
            new_state.element_id++;
            new_state.partial_codepoint = 0;
            Enqueue(new_state);
          }
        } else {
          // For positive classes, accept if codepoint IS in a range
          bool matches_range = false;
          for (int i = 1; i < sub_sequence.size(); i += 2) {
            if (new_state.partial_codepoint >= sub_sequence[i] &&
                new_state.partial_codepoint <= sub_sequence[i + 1]) {
              matches_range = true;
              break;
            }
          }
          if (matches_range) {
            new_state.element_id++;
            new_state.partial_codepoint = 0;
            Enqueue(new_state);
          }
        }
      } else {
        // Check if partial codepoint could still potentially match any range
        int32_t remaining_bytes = new_state.sub_element_id;
        int32_t min_codepoint = new_state.partial_codepoint << (6 * remaining_bytes);
        int32_t max_codepoint = min_codepoint | ((1 << (6 * remaining_bytes)) - 1);

        bool could_match = false;
        for (int i = 1; i < sub_sequence.size(); i += 2) {
          int32_t lower = sub_sequence[i];
          int32_t upper = sub_sequence[i + 1];
          if (max_codepoint >= lower && min_codepoint <= upper) {
            could_match = true;
            break;
          }
        }

        // For negative classes: always continue (will verify on final byte)
        // For positive classes: only continue if some range could match
        bool should_continue = is_negative ? true : could_match;
        if (should_continue) {
          tmp_states_to_be_added_.push_back(new_state);
        }
      }
    }
    return;
  }

  // Handle non-ASCII first bytes
  if (!isascii(ch)) {
    auto [accepted, num_bytes, partial] = HandleUTF8FirstByte(ch);
    if (!accepted) {
      return;
    }

    XGRAMMAR_DCHECK(num_bytes > 1);

    // Compute possible codepoint range for this first byte
    int32_t min_codepoint = partial << (6 * (num_bytes - 1));
    int32_t max_codepoint = min_codepoint | ((1 << (6 * (num_bytes - 1))) - 1);

    // Check if any stored range could potentially match
    bool could_match = false;
    for (int i = 1; i < sub_sequence.size(); i += 2) {
      int32_t lower = sub_sequence[i];
      int32_t upper = sub_sequence[i + 1];
      // Check for overlap between [min_codepoint, max_codepoint] and [lower, upper]
      if (max_codepoint >= lower && min_codepoint <= upper) {
        could_match = true;
        break;
      }
    }

    // For negative classes: accept if no range could match (will verify on final byte)
    // For positive classes: accept if some range could match (will verify on final byte)
    bool should_continue = is_negative ? true : could_match;

    if (should_continue) {
      auto new_state = state;
      new_state.sub_element_id = num_bytes - 1;
      new_state.partial_codepoint = partial;
      tmp_states_to_be_added_.push_back(new_state);
    }
    return;
  }

  // ASCII handling (unchanged)
  for (int i = 1; i < sub_sequence.size(); i += 2) {
    if (static_cast<uint8_t>(sub_sequence[i]) <= ch &&
        ch <= static_cast<uint8_t>(sub_sequence[i + 1])) {
      if (!is_negative) {
        auto new_state = state;
        new_state.element_id++;
        new_state.sub_element_id = 0;
        Enqueue(new_state);
      }
      return;
    }
  }
  if (is_negative) {
    auto new_state = state;
    new_state.element_id++;
    new_state.sub_element_id = 0;
    Enqueue(new_state);
  }
}

void EarleyParser::AdvanceCharacterClassStar(
    const ParserState& state, const uint8_t ch, const GrammarExpr& sub_sequence
) {
  XGRAMMAR_DCHECK(sub_sequence.type == GrammarExprType::kCharacterClassStar)
      << "The element type is not supported!";

  bool is_negative = static_cast<bool>(sub_sequence[0]);

  // The state is matching a UTF8 character (continuation bytes).
  if (state.sub_element_id > 0) {
    if ((ch & 0xC0) == 0x80) {
      auto new_state = state;
      new_state.sub_element_id--;
      // Accumulate the codepoint from continuation byte
      new_state.partial_codepoint = (new_state.partial_codepoint << 6) | (ch & 0x3F);

      // Check if the UTF8 character is completed.
      if (new_state.sub_element_id == 0) {
        if (is_negative) {
          // For negative classes, accept if codepoint is NOT in any range
          bool matches_range = false;
          for (int i = 1; i < sub_sequence.size(); i += 2) {
            if (new_state.partial_codepoint >= sub_sequence[i] &&
                new_state.partial_codepoint <= sub_sequence[i + 1]) {
              matches_range = true;
              break;
            }
          }
          if (!matches_range) {
            new_state.partial_codepoint = 0;
            Enqueue(new_state);
          }
        } else {
          // For positive classes, accept if codepoint IS in a range
          bool matches_range = false;
          for (int i = 1; i < sub_sequence.size(); i += 2) {
            if (new_state.partial_codepoint >= sub_sequence[i] &&
                new_state.partial_codepoint <= sub_sequence[i + 1]) {
              matches_range = true;
              break;
            }
          }
          if (matches_range) {
            new_state.partial_codepoint = 0;
            Enqueue(new_state);
          }
        }
      } else {
        // Check if partial codepoint could still potentially match any range
        int32_t remaining_bytes = new_state.sub_element_id;
        int32_t min_codepoint = new_state.partial_codepoint << (6 * remaining_bytes);
        int32_t max_codepoint = min_codepoint | ((1 << (6 * remaining_bytes)) - 1);

        bool could_match = false;
        for (int i = 1; i < sub_sequence.size(); i += 2) {
          int32_t lower = sub_sequence[i];
          int32_t upper = sub_sequence[i + 1];
          if (max_codepoint >= lower && min_codepoint <= upper) {
            could_match = true;
            break;
          }
        }

        // For negative classes: always continue (will verify on final byte)
        // For positive classes: only continue if some range could match
        bool should_continue = is_negative ? true : could_match;
        if (should_continue) {
          tmp_states_to_be_added_.push_back(new_state);
        }
      }
    }
    return;
  }

  // Handle non-ASCII first bytes
  if (!isascii(ch)) {
    auto [accepted, num_bytes, partial] = HandleUTF8FirstByte(ch);
    if (!accepted) {
      return;
    }

    XGRAMMAR_DCHECK(num_bytes > 1);

    // Compute possible codepoint range for this first byte
    int32_t min_codepoint = partial << (6 * (num_bytes - 1));
    int32_t max_codepoint = min_codepoint | ((1 << (6 * (num_bytes - 1))) - 1);

    // Check if any stored range could potentially match
    bool could_match = false;
    for (int i = 1; i < sub_sequence.size(); i += 2) {
      int32_t lower = sub_sequence[i];
      int32_t upper = sub_sequence[i + 1];
      // Check for overlap between [min_codepoint, max_codepoint] and [lower, upper]
      if (max_codepoint >= lower && min_codepoint <= upper) {
        could_match = true;
        break;
      }
    }

    // For negative classes: accept if no range could match (will verify on final byte)
    // For positive classes: accept if some range could match (will verify on final byte)
    bool should_continue = is_negative ? true : could_match;

    if (should_continue) {
      auto new_state = state;
      new_state.sub_element_id = num_bytes - 1;
      new_state.partial_codepoint = partial;
      tmp_states_to_be_added_.push_back(new_state);
    }
    return;
  }

  // ASCII handling (unchanged)
  for (int i = 1; i < sub_sequence.size(); i += 2) {
    if (static_cast<uint8_t>(sub_sequence[i]) <= ch &&
        ch <= static_cast<uint8_t>(sub_sequence[i + 1])) {
      if (!is_negative) {
        Enqueue(state);
      }
      return;
    }
  }
  if (is_negative) {
    Enqueue(state);
  }
}

void EarleyParser::AdvanceFsm(const ParserState& state, const uint8_t ch) {
  XGRAMMAR_DCHECK(state.rule_id != -1 && grammar_->per_rule_fsms[state.rule_id].has_value());
  const auto& current_fsm = grammar_->per_rule_fsms[state.rule_id].value();
  for (const auto& edge : current_fsm.GetFsm().GetFsm().GetEdges(state.element_id)) {
    if ((!edge.IsCharRange()) || ch < edge.min || ch > edge.max) {
      continue;
    }
    auto new_state = state;
    new_state.element_id = edge.target;
    if ((!current_fsm.GetFsm().IsNonTerminalState(edge.target)) &&
        (!current_fsm.GetFsm().IsEndState(edge.target) &&
         current_fsm.GetFsm().IsScanableState(edge.target))) {
      EnqueueWithoutProcessing(std::move(new_state));
    } else {
      Enqueue(std::move(new_state));
    }
  }
}

void EarleyParser::ScanAtomicToken(const ParserState& state, int32_t token_id) {
  if (state.rule_id == -1) return;
  XGRAMMAR_DCHECK(grammar_->per_rule_fsms[state.rule_id].has_value());
  const auto& current_fsm = grammar_->per_rule_fsms[state.rule_id].value();
  for (const auto& edge : current_fsm.GetFsm().GetFsm().GetEdges(state.element_id)) {
    bool matched = false;
    if (edge.IsToken()) {
      auto info = current_fsm.GetFsm().GetFsm().GetTokenEdgeInfo(edge.GetAuxIndex());
      matched = info.Contains(token_id);
    } else if (edge.IsExcludeToken()) {
      auto info = current_fsm.GetFsm().GetFsm().GetExcludeTokenEdgeInfo(edge.GetAuxIndex());
      matched = info.Accepts(token_id);
    }
    if (!matched) continue;
    auto new_state = state;
    new_state.element_id = edge.target;
    if ((!current_fsm.GetFsm().IsNonTerminalState(edge.target)) &&
        (!current_fsm.GetFsm().IsEndState(edge.target) &&
         current_fsm.GetFsm().IsScanableState(edge.target))) {
      EnqueueWithoutProcessing(std::move(new_state));
    } else {
      Enqueue(std::move(new_state));
    }
  }
}

bool EarleyParser::AdvanceAtomicToken(int32_t token_id, bool debug_print) {
  XGRAMMAR_DCHECK(tmp_process_state_queue_.empty())
      << "The tmp_process_state_queue_ should be empty before AdvanceAtomicToken.";
  tmp_states_visited_in_queue_.Clear();
  tmp_states_to_be_added_.clear();
  tmp_accept_stop_token_ = false;
  const auto& latest_states = scanable_state_history_[scanable_state_history_.size() - 1];
  for (const auto& state : latest_states) {
    ScanAtomicToken(state, token_id);
  }
  if (tmp_process_state_queue_.empty() && tmp_states_to_be_added_.empty()) {
    return false;
  }
  rule_id_to_completable_states_.PushBack(std::vector<std::pair<int32_t, ParserState>>());
  while (!tmp_process_state_queue_.empty()) {
    auto queued = tmp_process_state_queue_.PopFront();
    for (const auto& [begin, end] : queued.intervals) {
      auto state = queued.state;
      state.rule_start_pos = begin;
      processing_range_ = true;
      processing_range_begin_ = begin;
      processing_range_end_ = end;
      auto [scanable, completable] = Predict(state, debug_print);
      if (completable) {
        Complete(state, debug_print);
      }
      if (scanable) {
        AppendScannableRange(state, end);
      }
      processing_range_ = false;
    }
  }
  rule_id_to_completable_states_.FinalizeLatestRow();
  is_completed_.push_back(tmp_accept_stop_token_);
  scanable_state_history_.PushBack(tmp_states_to_be_added_);
  return true;
}

bool RepeatDetector::IsVisited(const ParserState& state) const {
  // If the size is larger than the threshold, then we use the set to check.
  if (size_ > transition_threshold_) {
    return visited_set_.find(state) != visited_set_.end();
  }
  return std::find_if(
             visited_vector_.begin(),
             visited_vector_.begin() + size_,
             [&state](const ParserState& s) { return StateEqualForParsing()(state, s); }
         ) != visited_vector_.begin() + size_;
}

void RepeatDetector::Insert(const ParserState& state) {
  if (size_ == transition_threshold_) {
    for (const auto& s : visited_vector_) {
      visited_set_.insert(s);
    }
  }
  size_++;
  if (size_ > transition_threshold_) {
    visited_set_.insert(state);
  } else {
    visited_vector_[size_ - 1] = state;
  }
}

void RepeatDetector::Clear() {
  if (size_ > transition_threshold_) {
    visited_set_.clear();
  }
  size_ = 0;
}

}  // namespace xgrammar
