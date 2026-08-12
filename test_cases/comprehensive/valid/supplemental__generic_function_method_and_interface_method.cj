func identity<T>(value: T): T { value }
interface Transform { func apply<T>(value: T): T }
class Transformer <: Transform { public init() {}
 public func apply<T>(value: T): T { value } }
main(): Unit { let value: String = identity<String>(Transformer().apply<String>("ok")) }
