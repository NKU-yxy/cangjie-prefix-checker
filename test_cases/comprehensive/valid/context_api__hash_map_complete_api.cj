main(): Unit { let map: HashMap<String, Int64> = HashMap<String, Int64>()
 map.add("one", 1)
 map.add([("two", 2)])
 let value: Int64 = map.get("one").getOrThrow()
 map.remove("one")
 map.remove(["two"])
 let inserted: Bool = map.addIfAbsent("three", 3)
 let keys: KeysView<String> = map.keys()
 let values: ValuesView<Int64> = map.values()
 let keySize: Int64 = keys.size()
 let valueSize: Int64 = values.size()
 let fieldSize: Int64 = map.size
 let fieldCapacity: Int64 = map.capacity
 let callSize: Int64 = map.size()
 let callCapacity: Int64 = map.capacity()
 map.replace("three", 4)
 let copy: HashMap<String, Int64> = map.clone()
 map.clear() }
