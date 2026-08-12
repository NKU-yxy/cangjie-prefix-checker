main(): Unit { let set: HashSet<Int64> = HashSet<Int64>()
 let added: Bool = set.add(1)
 set.add([2, 3])
 let inserted: Bool = set.addIfAbsent(4)
 let found: Bool = set.contains(1)
 let removed: Bool = set.remove(1)
 set.remove([2, 3])
 set.reserve(8)
 let copy: HashSet<Int64> = set.clone()
 let values: Array<Int64> = copy.toArray()
 let fieldSize: Int64 = set.size
 let fieldCapacity: Int64 = set.capacity
 let callSize: Int64 = set.size()
 let callCapacity: Int64 = set.capacity() }
