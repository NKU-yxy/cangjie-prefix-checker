interface Count { func count(): Int64 }
class Bad <: Count { public init() {}
 public func count(): String { "bad" } }
main(): Unit { println(0) }
