class Box { let value: Int64
 public init(initial: Int64) { value = initial }
 public func get(): Int64 { value } }
main(): Unit { let box: Box = Box(7)
 println(box.get()) }
