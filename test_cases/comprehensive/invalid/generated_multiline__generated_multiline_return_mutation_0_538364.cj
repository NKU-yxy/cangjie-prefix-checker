func combine_0_538364<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {
    merge(left, right)
}

main(): Unit {
    let result_0_538364: Bool =
        combine_0_538364<Bool>(
            true,
            false,
            { a: Bool,
               b: Bool =>
               314159 }
        )
}
