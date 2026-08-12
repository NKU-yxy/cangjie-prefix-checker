main(): Unit { let map: HashMap<String, Int64> = HashMap<String, Int64>()
 map.add("one", 1)
 let value: Int64 = map.get("one").getOrThrow()
 println(value) }
