// JavaScript source code
$(".open-button").on("click", function () {
    $(this).closest('.collapse-group').find('.collapse').collapse('show');
});

$(".close-button").on("click", function () {
    $(this).closest('.collapse-group').find('.collapse').collapse('hide');
});
