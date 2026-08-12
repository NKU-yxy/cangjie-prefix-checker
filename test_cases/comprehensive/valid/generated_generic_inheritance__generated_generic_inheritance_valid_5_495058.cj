interface Source_5_495058<A> {
    func get(): A
}

interface Middle_5_495058<B> <: Source_5_495058<B> {
    func get(): B
}

class Box_5_495058 <: Middle_5_495058<Bool> {
    let value: Bool
    public init(initial: Bool) { value = initial }
    public func get(): Bool { value }
}

main(): Unit {
    let item_5_495058: Source_5_495058<Bool> = Box_5_495058(true)
    let extracted_5_495058: Bool = item_5_495058.get()
}
