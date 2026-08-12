func twice(value: Int64, op: (Int64) -> Int64): Int64 { op(op(value)) }
main(): Unit { let inc: (Int64) -> Int64 = { x: Int64 => x + 1 }
 println(twice(3, inc)) }
