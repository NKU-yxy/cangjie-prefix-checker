func apply_7_479541<T>(value: T, action: (T) -> T): T {
    action(value)
}

main(): Unit {
    let answer_7_479541: Int64 = apply_7_479541<Int64>(
        16,
        { outer: Int64 => apply_7_479541<Int64>(
            outer,
            { level_2_7_479541: Int64 => apply_7_479541<Int64>(
                level_2_7_479541,
                { level_1_7_479541: Int64 => "nested-wrong" }
            ) }
        ) }
    )
}
