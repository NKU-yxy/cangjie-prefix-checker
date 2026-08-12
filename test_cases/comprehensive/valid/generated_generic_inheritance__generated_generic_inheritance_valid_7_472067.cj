interface Source_7_472067<A> {
    func get(): A
}

interface Middle_7_472067<B> <: Source_7_472067<B> {
    func get(): B
}

class Box_7_472067 <: Middle_7_472067<Int64> {
    let value: Int64
    public init(initial: Int64) { value = initial }
    public func get(): Int64 { value }
}

main(): Unit {
    let item_7_472067: Source_7_472067<Int64> = Box_7_472067(91)
    let extracted_7_472067: Int64 = item_7_472067.get()
}
