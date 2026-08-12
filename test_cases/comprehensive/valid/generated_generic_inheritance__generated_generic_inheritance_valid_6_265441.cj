interface Source_6_265441<A> {
    func get(): A
}

interface Middle_6_265441<B> <: Source_6_265441<B> {
    func get(): B
}

class Box_6_265441<C> <: Middle_6_265441<C> {
    let value: C
    public init(initial: C) { value = initial }
    public func get(): C { value }
}

main(): Unit {
    let item_6_265441: Source_6_265441<Bool> = Box_6_265441<Bool>(false)
    let extracted_6_265441: Bool = item_6_265441.get()
}
