interface Left {}
interface Right {}
class Both <: Left & Right { public init() {} }
main(): Unit { let item: Left = Both() }
