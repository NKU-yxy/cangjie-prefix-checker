#ifndef CANGJIE_G4_SYNTAX_H_
#define CANGJIE_G4_SYNTAX_H_

#include <memory>
#include <stdexcept>
#include <string>

namespace cangjie::g4 {

class UpstreamError final : public std::runtime_error {
 public:
  UpstreamError(std::string kind, const std::string& message);

  const std::string& kind() const noexcept { return kind_; }

 private:
  std::string kind_;
};

class SyntaxMatcher final {
 public:
  explicit SyntaxMatcher(const std::string& grammar_source);
  ~SyntaxMatcher();

  SyntaxMatcher(SyntaxMatcher&&) noexcept;
  SyntaxMatcher& operator=(SyntaxMatcher&&) noexcept;

  SyntaxMatcher(const SyntaxMatcher&) = delete;
  SyntaxMatcher& operator=(const SyntaxMatcher&) = delete;

  bool AcceptString(const std::string& fragment);

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace cangjie::g4

#endif  // CANGJIE_G4_SYNTAX_H_
