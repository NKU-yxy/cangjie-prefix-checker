interface Value_3_885957 {
    func value(): Int64
}

class Counter_3_885957 <: Value_3_885957 {
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
    let counter_3_885957: Value_3_885957 = Counter_3_885957(3)
    let result_3_885957: Int64 = counter_3_885957.value()
}
