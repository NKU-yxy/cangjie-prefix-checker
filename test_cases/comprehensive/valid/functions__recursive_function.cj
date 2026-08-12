func fact(n: Int64): Int64 { if (n <= 1) { 1 } else { n * fact(n - 1) } }
main(): Unit { println(fact(5)) }
