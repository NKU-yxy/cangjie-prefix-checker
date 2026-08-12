interface Source_3_427178<A> {
    func get(): A
}

interface Middle_3_427178<B> <: Source_3_427178<B> {
    func get(): B
}

class Box_3_427178 <: Middle_3_427178<Bool> {
    let value: Bool
    public init(initial: Bool) { value = initial }
    public func get(): Bool { value }
}

main(): Unit {
    let item_3_427178: Source_3_427178<Int64> = Box_3_427178(true)
    let extracted_3_427178: Bool = item_3_427178.get()
}
