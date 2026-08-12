func apply_6_512376<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_6_512376: Int64 = apply_6_512376<Int64>(
        10,
        { outer: Int64 => apply_6_512376<Int64>(
            outer,
            { level_4_6_512376: Int64 => apply_6_512376<Int64>(
                level_4_6_512376,
                { level_3_6_512376: Int64 => apply_6_512376<Int64>(
                    level_3_6_512376,
                    { level_2_6_512376: Int64 => apply_6_512376<Int64>(
                        level_2_6_512376,
                        { level_1_6_512376: Int64 => "nested-wrong" }
                    ) }
                ) }
            ) }
        ) }
    )
}
