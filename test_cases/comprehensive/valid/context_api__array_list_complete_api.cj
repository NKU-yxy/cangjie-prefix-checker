main(): Unit { let a: ArrayList<Int64> = ArrayList<Int64>()
 let b: ArrayList<Int64> = ArrayList<Int64>()
 let empty: Bool = a.isEmpty()
 a.add(1)
 a.add(b)
 a.add(2, 0)
 a.add(b, 0)
 a.remove(0)
 a.reserve(8)
 a.reverse()
 let copy: ArrayList<Int64> = a.clone()
 let values: Array<Int64> = copy.toArray()
 let size: Int64 = a.size
 let capacity: Int64 = a.capacity
 a.clear() }
