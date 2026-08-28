main(): Unit { let array: Array<Int64> = [1, 2]
 let arrayIndex: Optional<Int64> = array.indexOf(2)
 let list: ArrayList<Int64> = ArrayList<Int64>([1, 2])
 let listValue: Optional<Int64> = list.get(0)
 let map: HashMap<String, Int64> = HashMap<String, Int64>()
 let hasKey: Bool = map.contains("key")
 let set: HashSet<Int64> = HashSet<Int64>()
 set.clear()
 let some: Bool = arrayIndex.isSome()
 let none: Bool = arrayIndex.isNone()
 let fallback: Int64 = arrayIndex.orElse(0)
 let textIndex: Optional<Int64> = "alpha".indexOf("ph") }
