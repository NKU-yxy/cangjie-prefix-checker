func combine_6_971114<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_6_971114: Int64 =
        combine_6_971114<Int64>(
            26,
            93,
            { a: Int64,
               b: Int64 =>
               a + b }
        )
}
