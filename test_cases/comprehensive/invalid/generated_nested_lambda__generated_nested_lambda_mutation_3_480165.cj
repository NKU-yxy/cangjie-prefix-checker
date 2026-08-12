func apply_3_480165<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_3_480165: Int64 = apply_3_480165<Int64>(
        1,
        { outer: Int64 => apply_3_480165<Int64>(
            outer,
            { level_2_3_480165: Int64 => apply_3_480165<Int64>(
                level_2_3_480165,
                { level_1_3_480165: Int64 => "nested-wrong" }
            ) }
        ) }
    )
}
