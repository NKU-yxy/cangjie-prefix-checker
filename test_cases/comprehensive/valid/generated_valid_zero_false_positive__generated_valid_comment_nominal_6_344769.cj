interface Value_6_344769 {
    func value(): Int64
}

class Counter_6_344769 <: Value_6_344769 {
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
    let counter_6_344769: Value_6_344769 = Counter_6_344769(3)
    let result_6_344769: Int64 = counter_6_344769.value()
}
