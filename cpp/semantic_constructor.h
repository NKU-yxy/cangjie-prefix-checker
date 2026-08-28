#pragma once

#include "native_semantic.h"

#include <string_view>

namespace cangjie {

// 检查构造器退出前是否初始化了所有必需字段。
CheckStatus CheckConstructorFieldInitialization(std::string_view source);

}
