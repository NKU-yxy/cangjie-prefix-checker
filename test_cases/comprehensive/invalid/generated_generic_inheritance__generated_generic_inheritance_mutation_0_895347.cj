interface Source_0_895347<A> {
    func get(): A
}

interface Middle_0_895347<B> <: Source_0_895347<B> {
    func get(): B
}

class Box_0_895347<C> <: Middle_0_895347<C> {
    let value: C
    public init(initial: C) { value = initial }
    public func get(): C { value }
}

main(): Unit {
    let item_0_895347: Source_0_895347<String> = Box_0_895347<Int64>(90)
    let extracted_0_895347: Int64 = item_0_895347.get()
}
