interface Source_1_330723<A> {
    func get(): A
}

interface Middle_1_330723<B> <: Source_1_330723<B> {
    func get(): B
}

class Box_1_330723 <: Middle_1_330723<Int64> {
    let value: Int64
    public init(initial: Int64) { value = initial }
    public func get(): Int64 { value }
}

main(): Unit {
    let item_1_330723: Source_1_330723<Int64> = Box_1_330723(88)
    let extracted_1_330723: Int64 = item_1_330723.get()
}
