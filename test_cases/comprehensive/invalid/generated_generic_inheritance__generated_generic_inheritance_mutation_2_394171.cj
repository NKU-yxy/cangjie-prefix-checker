interface Source_2_394171<A> {
    func get(): A
}

interface Middle_2_394171<B> <: Source_2_394171<B> {
    func get(): B
}

class Box_2_394171<C> <: Middle_2_394171<C> {
    let value: C
    public init(initial: C) { value = initial }
    public func get(): C { value }
}

main(): Unit {
    let item_2_394171: Source_2_394171<String> = Box_2_394171<Int64>(65)
    let extracted_2_394171: Int64 = item_2_394171.get()
}
