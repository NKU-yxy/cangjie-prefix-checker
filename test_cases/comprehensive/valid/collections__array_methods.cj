main(): Unit { let xs: Array<Int64> = Array<Int64>(3, 7)
 xs.swap(0, 2)
 xs.fill(9)
 let ys: Array<Int64> = xs.clone()
 println(ys.size) }
