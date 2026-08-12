interface Named { func name(): String }
class User <: Named { public init() {}
 public func name(): String { "Ada" } }
main(): Unit { let item: Named = User()
 println(item.name()) }
