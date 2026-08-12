interface Source<T> { func get(): T }
class Holder<T> <: Source<T> { let value: T
 public init(v: T) { value = v }
 public func get(): T { value } }
main(): Unit { let source: Source<String> = Holder<Int64>(9)
 println(0) }
