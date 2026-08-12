class Box<T> { public init(value: T) {} }
main(): Unit { let box: Box<Int64, String> = Box<Int64, String>(1) }
