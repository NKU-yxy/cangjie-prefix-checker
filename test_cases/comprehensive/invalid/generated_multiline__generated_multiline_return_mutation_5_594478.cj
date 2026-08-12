func combine_5_594478<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_5_594478: Int64 =
        combine_5_594478<Int64>(
            16,
            94,
            { a: Int64,
               b: Int64 =>
               "wrong" }
        )
}
