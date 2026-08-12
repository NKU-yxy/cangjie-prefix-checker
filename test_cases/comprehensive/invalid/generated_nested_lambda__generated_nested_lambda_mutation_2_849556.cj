func apply_2_849556<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_2_849556: Int64 = apply_2_849556<Int64>(
        19,
        { outer: Int64 => apply_2_849556<Int64>(
            outer,
            { level_3_2_849556: Int64 => apply_2_849556<Int64>(
                level_3_2_849556,
                { level_2_2_849556: Int64 => apply_2_849556<Int64>(
                    level_2_2_849556,
                    { level_1_2_849556: Int64 => "nested-wrong" }
                ) }
            ) }
        ) }
    )
}
