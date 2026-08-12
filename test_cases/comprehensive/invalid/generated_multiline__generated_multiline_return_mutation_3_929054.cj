func combine_3_929054<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_3_929054: Bool =
        combine_3_929054<Bool>(
            true,
            false,
            { a: Bool,
               b: Bool =>
               314159 }
        )
}
