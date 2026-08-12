func combine_4_039311<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_4_039311: Int64 =
        combine_4_039311<Int64>(
            15,
            87,
            { a: Int64,
               b: Int64 =>
               "wrong" }
        )
}
