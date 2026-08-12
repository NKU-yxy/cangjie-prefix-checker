class Key <: Hashable & Equatable<Key> { public init() {}
 public func hashCode(): Int64 { 1 }
 public func equals(other: Key): Bool { true } }
class Items <: Collection<Int64> & Iterable<Int64> { public init() {}
 public func size(): Int64 { 0 } }
main(): Unit { let key: Hashable = Key()
 println(key.hashCode()) }
