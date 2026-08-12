interface Value_4_722197 {
    func value(): Int64
}

class Counter_4_722197 <: Value_4_722197 {
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
    let counter_4_722197: Value_4_722197 = Counter_4_722197(2)
    let result_4_722197: Int64 = counter_4_722197.value()
}
