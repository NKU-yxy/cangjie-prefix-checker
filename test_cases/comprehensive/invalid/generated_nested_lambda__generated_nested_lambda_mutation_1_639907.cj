func apply_1_639907<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_1_639907: Int64 = apply_1_639907<Int64>(
        13,
        { outer: Int64 => apply_1_639907<Int64>(
            outer,
            { level_2_1_639907: Int64 => apply_1_639907<Int64>(
                level_2_1_639907,
                { level_1_1_639907: Int64 => "nested-wrong" }
            ) }
        ) }
    )
}
