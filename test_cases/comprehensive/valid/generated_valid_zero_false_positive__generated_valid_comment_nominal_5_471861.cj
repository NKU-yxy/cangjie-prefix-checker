interface Value_5_471861 {
    func value(): Int64
}

class Counter_5_471861 <: Value_5_471861 {
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
    let counter_5_471861: Value_5_471861 = Counter_5_471861(5)
    let result_5_471861: Int64 = counter_5_471861.value()
}
