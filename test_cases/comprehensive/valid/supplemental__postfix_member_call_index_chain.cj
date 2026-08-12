class Store { let rows: Array<Array<Int64>>
 public init(values: Array<Array<Int64>>) { rows = values }
 public func all(): Array<Array<Int64>> { rows } }
main(): Unit { let value: Int64 = Store([[1]]).all()[0][0]
 println(value) }
