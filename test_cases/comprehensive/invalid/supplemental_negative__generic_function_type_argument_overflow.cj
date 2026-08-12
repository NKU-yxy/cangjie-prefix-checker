func id<T>(value: T): T { value }
main(): Unit { let value: Int64 = id<Int64, String>(1) }
