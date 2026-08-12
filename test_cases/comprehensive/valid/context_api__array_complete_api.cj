main(): Unit { let a: Array<Int64> = [1, 2, 3]
 let size: Int64 = a.size
 let gotOption: Optional<Int64> = a.get(0)
 let got: Int64 = gotOption.getOrThrow()
 a.fill(4)
 a.swap(0, 1)
 let part: Array<Int64> = a.slice(0, 2)
 let copy: Array<Int64> = a.clone()
 let joined: Array<Int64> = a.concat(copy)
 a.reverse()
 let firstOption: Optional<Int64> = a.first()
 let first: Int64 = firstOption.getOrThrow()
 let lastOption: Optional<Int64> = a.last()
 let last: Int64 = lastOption.getOrThrow() }
