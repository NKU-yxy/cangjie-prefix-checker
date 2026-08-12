interface Value_1_954037 {
    func value(): Int64
}

class Counter_1_954037 <: Value_1_954037 {
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
    let counter_1_954037: Value_1_954037 = Counter_1_954037(5)
    let result_1_954037: Int64 = counter_1_954037.value()
}
