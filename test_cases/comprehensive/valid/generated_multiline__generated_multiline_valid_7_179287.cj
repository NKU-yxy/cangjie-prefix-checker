func combine_7_179287<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_7_179287: String =
        combine_7_179287<String>(
            "left-7",
            "right-7",
            { a: String,
               b: String =>
               a.concat(b) }
        )
}
