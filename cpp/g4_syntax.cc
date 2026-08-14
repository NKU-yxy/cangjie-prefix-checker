#include "g4_syntax.h"

#include <utility>
#include <vector>

// This translation unit is intentionally the only project TU that sees the
// vendored public headers.  The preprocessor rename must also be supplied when
// every vendored XGrammar core .cc file is compiled.
#define xgrammar xgrammar_g4
#include <xgrammar/xgrammar.h>
#undef xgrammar

namespace cangjie::g4 {

UpstreamError::UpstreamError(std::string kind, const std::string& message)
    : std::runtime_error(message), kind_(std::move(kind)) {}

class SyntaxMatcher::Impl {
 public:
  explicit Impl(const std::string& grammar_source)
      : tokenizer_(std::vector<std::string>{"x"}, xgrammar_g4::VocabType::RAW),
        compiler_(tokenizer_, 1, false),
        compiled_(compiler_.CompileGrammar(grammar_source)),
        matcher_(compiled_) {}

  bool AcceptString(const std::string& fragment) {
    return matcher_.AcceptString(fragment);
  }

 private:
  xgrammar_g4::TokenizerInfo tokenizer_;
  xgrammar_g4::GrammarCompiler compiler_;
  xgrammar_g4::CompiledGrammar compiled_;
  xgrammar_g4::GrammarMatcher matcher_;
};

SyntaxMatcher::SyntaxMatcher(const std::string& grammar_source) {
  try {
    impl_ = std::make_unique<Impl>(grammar_source);
  } catch (const xgrammar_g4::XGrammarError& error) {
    throw UpstreamError(error.GetType(), error.what());
  }
}

SyntaxMatcher::~SyntaxMatcher() = default;
SyntaxMatcher::SyntaxMatcher(SyntaxMatcher&&) noexcept = default;
SyntaxMatcher& SyntaxMatcher::operator=(SyntaxMatcher&&) noexcept = default;

bool SyntaxMatcher::AcceptString(const std::string& fragment) {
  try {
    return impl_->AcceptString(fragment);
  } catch (const xgrammar_g4::XGrammarError& error) {
    throw UpstreamError(error.GetType(), error.what());
  }
}

}  // namespace cangjie::g4
