interface Convert { func convert(value: Int64): String }
class Bad <: Convert { public init() {}
 public func convert(value: String): String { value } }
main(): Unit { println(0) }
