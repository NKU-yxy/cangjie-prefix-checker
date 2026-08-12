interface Value_2_887597 {
    func value(): Int64
}

class Counter_2_887597 <: Value_2_887597 {
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
    let counter_2_887597: Value_2_887597 = Counter_2_887597(5)
    let result_2_887597: Int64 = counter_2_887597.value()
}
