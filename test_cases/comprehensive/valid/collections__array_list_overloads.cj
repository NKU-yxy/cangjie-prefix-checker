main(): Unit { let xs: ArrayList<Int64> = ArrayList<Int64>()
 xs.add(1)
 xs.add(2, 0)
 let ys: Array<Int64> = xs.toArray()
 println(ys.size) }
