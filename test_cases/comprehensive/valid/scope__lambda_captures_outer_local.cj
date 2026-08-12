main(): Unit { let base: Int64 = 10
 let add: (Int64) -> Int64 = { x: Int64 => x + base }
 println(add(2)) }
