interface Source_4_049033<A> {
    func get(): A
}

interface Middle_4_049033<B> <: Source_4_049033<B> {
    func get(): B
}

class Box_4_049033<C> <: Middle_4_049033<C> {
    let value: C
    public init(initial: C) { value = initial }
    public func get(): C { value }
}

main(): Unit {
    let item_4_049033: Source_4_049033<String> = Box_4_049033<String>("value-4")
    let extracted_4_049033: String = item_4_049033.get()
}
