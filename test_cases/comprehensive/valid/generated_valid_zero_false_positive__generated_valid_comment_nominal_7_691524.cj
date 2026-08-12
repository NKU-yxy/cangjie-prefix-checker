interface Value_7_691524 {
    func value(): Int64
}

class Counter_7_691524 <: Value_7_691524 {
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
    let counter_7_691524: Value_7_691524 = Counter_7_691524(5)
    let result_7_691524: Int64 = counter_7_691524.value()
}
