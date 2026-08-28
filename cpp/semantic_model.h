#pragma once

#include <cstddef>
#include <iosfwd>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace cangjie {

// 保存一个函数或构造函数的规范化签名。
struct FunctionSig {
    std::string name;
    std::vector<std::string> type_params;
    std::vector<std::string> param_names;
    std::vector<std::string> param_types;
    std::string result = "Unit";
    std::size_t required = 0;  // 没有默认值的必传参数数量。
    bool is_static = false;
};

// 保存类、接口或结构体的成员和继承信息。
struct NominalInfo {
    std::string name;
    bool is_interface = false;
    std::vector<std::string> type_params;
    std::vector<std::string> supers;
    std::unordered_map<std::string, std::string> fields;
    std::unordered_map<std::string, std::string> static_fields;
    std::unordered_map<std::string, std::vector<FunctionSig>> methods;
    std::unordered_map<std::string, std::vector<FunctionSig>> static_methods;
    std::vector<FunctionSig> constructors;
};

// 汇总当前上下文和源码中可见的符号模型。
struct Model {
    std::unordered_map<std::string, std::vector<FunctionSig>> functions;
    std::unordered_map<std::string, NominalInfo> nominals;
    std::unordered_map<std::string, std::string> globals;
};

// 判断类型是否为有符号整数类型。
bool IsInteger(std::string_view type);
// 判断类型是否为浮点类型。
bool IsFloat(std::string_view type);
// 判断类型是否可参与数值运算。
bool IsNumeric(std::string_view type);
// 判断两个数值类型是否可直接兼容。
bool SameNumericFamily(std::string_view left, std::string_view right);
// 判断规范化文本是否为函数类型。
bool IsFunctionType(std::string_view type);
// 从二进制上下文表加载预置模型。
void LoadContextTable(const std::string& path, Model* model);
// 把模型输出为稳定的 Context IR JSON。
void DumpModelJson(std::ostream& os, const Model& model);

}
