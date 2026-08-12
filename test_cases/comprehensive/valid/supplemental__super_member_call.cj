class Base { public init() {}
 public func value(): Int64 { 1 } }
class Child <: Base { public init() {}
 public func value(): Int64 { super.value() } }
main(): Unit { println(Child().value()) }
