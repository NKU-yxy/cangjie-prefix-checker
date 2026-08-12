func combine_1_851143<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_1_851143: String =
        combine_1_851143<String>(
            "left-1",
            "right-1",
            { a: String,
               b: String =>
               a.concat(b) }
        )
}
