func combine_2_704070<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_2_704070: String =
        combine_2_704070<String>(
            "left-2",
            "right-2",
            { a: String,
               b: String =>
               314159 }
        )
}
