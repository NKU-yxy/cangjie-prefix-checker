interface Value_0_072625 {
    func value(): Int64
}

class Counter_0_072625 <: Value_0_072625 {
    let stored: Int64
    public init(initial: Int64) {
        // constructor assignment remains valid across a line comment
        stored = initial
    }
    public func value(): Int64 {
        stored
    }
}

main(): Unit {
    let counter_0_072625: Value_0_072625 = Counter_0_072625(6)
    let result_0_072625: Int64 = counter_0_072625.value()
}
