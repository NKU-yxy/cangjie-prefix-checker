func compose(f: (Int64) -> Int64): (Int64) -> Int64 { { x: Int64 => f(f(x)) } }
main(): Unit {}
